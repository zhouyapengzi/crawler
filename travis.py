import requests
import logging
import re
import os
import csv
import argparse,sys


total_builds_need_to_collect = 25
def get_all_builds(travis_url, headers):
    builds = []
    total_collect_builds = 0

    # travis result is paginated, return 25 results for each request.
    if 'travis-ci.org' in travis_url:
        response = requests.get(travis_url)
    else:
        response = requests.get(travis_url, headers = headers)
    if response.ok:
        response = response.json()
        # add the 25 to builds.
        total_collect_builds += len(response)
        builds += response
    else:
        logging.info(response.reason)

    # if need to collect more than 25
    # https://api.travis-ci.com/repos/flink-ci/flink/builds?after_number=9931
    while total_collect_builds < total_builds_need_to_collect:
        next_url = travis_url + '?after_number=' + response[-1]['number']
        if 'travis-ci.org' in travis_url:
            next_response = requests.get(next_url)
        else:
            next_response = requests.get(next_url, headers=headers)

        if next_response.ok:
            next_response = next_response.json()
            total_collect_builds += len(next_response)
            builds += next_response
            response = next_response
        else:
            break

    # can get build id and build number, branch, and so on.
    # I hope can know which branch it is in.
    logging.info('collect %s builds...' % total_collect_builds)

    return builds


def analyze_test(builds, headers, output_directory,project_name):
    output_file = os.path.join(output_directory, 'BuildSummary.csv')
    with open(output_file, 'a') as wf:
        wf_writer = csv.writer(wf)
        wf_writer.writerow(
            ["Build_ID", "Number", "TimeStamp",'Build_Commit', 'Build_Branch', 'Build_Status'])
        for build in builds:
            build_date = build['started_at']
            wf_writer.writerow(
                [str(build['id']), build['number'], build_date, build['commit'], build['branch'], build['state']])
            analyze_job(build, headers, output_directory,project_name)
    wf.close()


# flink, only get 'job stage' = 'test'
def analyze_job(build, headers, output_directory, project_name):
    out = os.path.join(output_directory, str(build['id']) + '.csv')
    if os.path.exists(out):
        return
    with open(out, 'w') as of:
        file_writer = csv.writer(of)
        file_writer.writerow(['ClassName', 'Duration', 'Build_id.', 'Build_Date', 'Job_id', 'Job_Status'])

        logging.info('parsing test report result for build:' + build['number'] + ' id:' + str(build['id']))

        if project_name == 'flink':
            job_url = 'https://api.travis-ci.com/v3/build/' + str(build['id']) + '/jobs'
        if project_name == 'jclouds' or project_name == 'cucumber':
            job_url = 'https://api.travis-ci.org/v3/build/' + str(build['id']) + '/jobs'


        jobs_response = requests.get(job_url, headers)
        if jobs_response.ok:
            jobs = jobs_response.json()['jobs']
            for job in jobs:
                logging.info(
                    'job:' + str(job['id']) + ' is ' + job['state'] )
                if job['state'] == 'canceled' or job['state'] == 'created':
                    logging.info('skip.')
                    continue

                # for cucumber, select the second job
                if project_name == 'cucumber':
                    if '.2' not in job['number']:
                        continue

                # for flink:
                if project_name =='flink':
                    if job['stage']['name'] == 'compile' or job['stage']['name'] == 'cleanup':
                        logging.info('skip.')
                        continue
                    job_id = job['id']
                    log_url = 'https://api.travis-ci.com/v3/job/' + str(job_id) + '/log'
                    log_response = requests.get(log_url, headers)

                if project_name == 'jclouds' or project_name == 'cucumber':
                    job_id = job['id']
                    log_url = 'https://api.travis-ci.org/v3/job/' + str(job_id) + '/log'
                    log_response = requests.get(log_url)

                if log_response.ok:
                    log = log_response.json()
                    log_content = log['content']
                    if log_content is not None:
                        if project_name == 'flink':
                            tests = find_test_log_flink(log_content)
                        if project_name == 'jclouds':
                            tests = find_test_log_jclouds(log_content)
                        if project_name == 'cucumber':
                            tests = find_test_log_cucumber(log_content)

                        if tests is None:
                            continue
                        # dump the tests dictionary to csv
                        for t in tests:
                            file_writer.writerow(
                                [t['test_class'], t['test_duration'], build['id'], build['started_at'],
                                 job_id, job['state']])
                else:
                    logging.error('Found no log....something is wrong, please manual check it!')
        of.close()


def find_test_log_flink(log_content):
    tests = []
    keys = []
    travis_control_regex = re.compile('\$ \./tools/travis_controller\.sh\s\S*\s')
    test_regex = re.compile('Tests\srun:\s\d*,\sFailures:\s\d*,\sErrors:\s\d*,\sSkipped:\s\d*,\sTime\selapsed:\s\d*[\.]\d*.*?\\n')
    control_result = travis_control_regex.search(log_content)
    if control_result:
        control_result = control_result.group(0).split()
        # flink: skip python jobs.
        if control_result[-1] == 'python':
            logging.info('skip python tests for flink...')
            return
    test_logs = test_regex.findall(log_content)
    if test_logs is None:
        logging.info('found no tests in the job.... maybe need to manual check')
        return

    print(len(test_logs))
    for test_log in test_logs:
        test = {}
        test_log = test_log.replace(',', ' ')
        t = test_log.split()
        # test['test_run'] = t[2]
        # test['test_failures'] = t[4]
        # test['test_errors'] = t[6]
        # test['test_skip'] = t[8]
        test['test_duration'] = t[11]
        test['test_class'] = t[-1]
        if test['test_class'] in keys:
            for tmp in tests:
                if tmp['test_class'] == test['test_class']:
                    tmp['test_duration'] += test['test_duration']
        else:
            tests.append(test)
            keys.append(test['test_class'])
    return tests


def find_test_log_jclouds(log_content):
    tests = []
    keys = []
    # test_regex = re.compile('Test\s.*?\(.*?\).*?\s')
    test_regex = re.compile('Test\s.*?\(.*?\)\s.*?\n')
    test_logs = test_regex.findall(log_content)
    if test_logs == None:
        logging.info('found no tests in the job.... maybe need to manual check')
        return
    print(len(test_logs))

    for test_log in test_logs:
        test = {}
        if 'skipped.' in test_log or 'failed' in test_log:
            continue
        if 'succeeded' not in test_log:
            print("something is wrong.")
            logging.error('something is wrong, need manual check.')
        t = test_log.split()
        test_class = t[1][t[1].find('(') + 1:t[1].find(')')]
        test_duration = (int)(t[-1].replace('ms',''))/1000
        test['test_class'] = test_class
        test['test_duration'] = test_duration

        if test_class in keys:
            for tmp in tests:
                if tmp['test_class'] == test_class:
                    tmp['test_duration'] += test_duration
        else:
            tests.append(test)
            keys.append(test_class)
    return tests


def find_test_log_cucumber(log_content):
    tests = []
    keys = []
    log_content = remove_color_code(log_content)
    test_regex = re.compile(
        'Tests\srun:\s\d*,\sFailures:\s\d*,\sErrors:\s\d*,\sSkipped:\s\d*,\sTime\selapsed:\s\d*[\.]\d*.*?\n')
    test_logs = test_regex.findall(log_content)
    if test_logs is None:
        logging.info('found no tests in the job.... maybe need to manual check')
        return

    print(len(test_logs))
    for test_log in test_logs:
        test = {}
        # print(test_log)
        # test_log = remove_color_code(test_log)
        test_log = test_log.replace(',', ' ')
        # print(test_log)
        t = test_log.split()
        test['test_duration'] = t[11]
        test['test_class'] = t[-1]
        if test['test_class'] in keys:
            for tmp in tests:
                if tmp['test_class'] == test['test_class']:
                    tmp['test_duration'] += test['test_duration']
        else:
            tests.append(test)
            keys.append(test['test_class'])
    return tests


def remove_color_code(s):
    ansi_escape = re.compile(r'''
        \x1B  # ESC
        (?:   # 7-bit C1 Fe (except CSI)
            [@-Z\\-_]
        |     # or [ for CSI, followed by a control sequence
            \[
            [0-?]*  # Parameter bytes
            [ -/]*  # Intermediate bytes
            [@-~]   # Final byte
        )
    ''', re.VERBOSE)
    result = ansi_escape.sub('',s)
    return result

# def find_test_log_guava(log_content):
#     tests = []
#     keys = []
#     #test_regex = re.compile('Tests\srun:\s\d*,\sFailures:\s\d*,\sErrors:\s\d*,\sSkipped:\s\d*,\sTime\selapsed:\s\d*[\.]\d*.*?\\n')
#     test_regex = re.compile('Running\s.*?\nTests\srun:\s\d*,\sFailures:\s\d*,\sErrors:\s\d*,\sSkipped:\s\d*,\sTime\selapsed:\s\d*[\.]\d*.*?\n')
#     test_logs = test_regex.findall(log_content)
#     if test_logs is None:
#         logging.info('found no tests in the job.... maybe need to manual check')
#         return
#
#     print(len(test_logs))
#     for test_log in test_logs:
#         test = {}
#         print(test_log)
#         test_log = test_log.replace('\n', ' ')
#         test_log = test_log.replace(',', ' ')
#
#         t = test_log.split()
#         test['test_duration'] = t[13]
#         test['test_class'] = t[1]
#         if test['test_class'] in keys:
#             for tmp in tests:
#                 if tmp['test_class'] == test['test_class']:
#                     tmp['test_duration'] += test['test_duration']
#         else:
#             tests.append(test)
#             keys.append(test['test_class'])
#     return tests


def create_output_directory(project):
    # create output folder for the project: output/project_name
    if not os.path.isdir('output'):
        os.mkdir('output')
    output_path = os.path.join('output', project)
    if not os.path.isdir(output_path):
        os.mkdir(output_path)
    return output_path


def main(argv):
    travis_token = 'PxrNXYx-UeVMYl2KlaxOMQ'
    headers = {'Authorization': 'token ' + travis_token}

    parser = argparse.ArgumentParser(description='crawl test result from Travis')
    parser.add_argument('project_name', type=str, metavar='project_name', help='name of the project. e.g. flink')
    args = parser.parse_args(argv)

    project_name = args.project_name
    output_directory = create_output_directory(project_name)

    travis_url = 'https://api.travis-ci.com/repos/'
    if project_name == 'flink':
        travis_url = 'https://api.travis-ci.com/repos/flink-ci/flink/builds'
    if project_name == 'jclouds':
        travis_url = 'https://api.travis-ci.org/repos/apache/jclouds/builds'
    if project_name == 'cucumber':
        travis_url = 'https://api.travis-ci.org/repos/cucumber/cucumber-jvm/builds'

    builds = get_all_builds(travis_url, headers)
    analyze_test(builds, headers, output_directory, project_name)


if __name__ == '__main__':
    logging.getLogger().setLevel(getattr(logging, 'INFO'))
    # sys.argv = ['travis.py', 'cucumber']
    main(sys.argv[1:])

