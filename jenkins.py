import json
import csv
import logging
import datetime
import os
import argparse, sys
import requests


def get_build(jenkins_url, output_directory):
    logging.info('Processing build batch for ' + jenkins_url )
    response = json.loads(requests.get(jenkins_url).text)
    builds = []
    output_file = os.path.join(output_directory,'BuildSummary.csv')
    with open(output_file, 'a') as wf:
        wf_writer = csv.writer(wf)
        wf_writer.writerow(["JobName","ID","URL","TimeStamp","Result","Test_TotalCount",'Test_SkipCount','test_FailCount'])
        for build in response["builds"]:
            build_url = build["url"]
            builds.append(build_url)
            build_time_stamp = datetime.datetime.utcfromtimestamp(build['timestamp'] / 1000).isoformat()

            build_total_count = '0'
            build_skip_count = '0'
            build_fail_count = '0'
            for action in build['actions']:
                if 'totalCount' in action.keys():
                    build_total_count = action['totalCount']
                    build_skip_count = action['skipCount']
                    build_fail_count = action['failCount']
            wf_writer.writerow([build['fullDisplayName'], str(build['number']), str(build_url),
                               build_time_stamp, str(build['result']), str(build_total_count),
                               str(build_skip_count), str(build_fail_count)])
    wf.close()
    print('total builds available: %s' % len(builds))
    logging.info('total builds available: %s' % len(builds))
    logging.info('save build summary to :' + output_file)
    return builds


def verify_test_report_exist(build_url):
    if not requests.get(build_url).ok:
        return False
    return True


def get_test_report_cxf(builds, output_directory):
    for build_url in builds:
        build_no = build_url[build_url[:build_url.rfind('/')].rfind('/') + 1: build_url.rfind('/')]
        build_slow_url = build_url + 'testReport/api/json?depth=2'
        logging.info('parsing test report result for build:' + build_url)

        if not verify_test_report_exist(build_slow_url):
            logging.info("build has no test report, skip:" + build_url)
            continue
        response = json.loads(requests.get(build_slow_url).text)

        out_file = os.path.join(output_directory, build_no + '_detail_bk.json')
        if not os.path.exists(out_file):
            output_detail_file = open(out_file, 'w')
            output_detail_file.write(json.dumps(response, indent=4, sort_keys=True))
            output_detail_file.close()
            logging.info("store raw crawl info as json to :" + output_detail_file.name)

        out = os.path.join(output_directory, build_no + '.csv')
        if os.path.exists(out):
            continue
        with open(out, 'w') as of:
            file_writer = csv.writer(of)
            file_writer.writerow(['ClassName', 'Duration'])

            if 'junit.TestResult' not in response['_class']:
                response = response['childReports']

            if len(response) > 0:
                for child in response:
                    test_response = child['result']
                    if 'junit.TestResult' in test_response['_class']:
                        cases = test_response['suites']
                        for case in cases:
                            class_duration = 0
                            class_name = ""
                            for tests in case['cases']:
                                class_duration += tests['duration']
                                class_name = tests['className']
                            file_writer.writerow([class_name, str(class_duration)])
        of.close()
        logging.info("test result saved to file: " + out)


def get_test_report(builds,output_directory):
    for build_url in builds:
        build_no = build_url[build_url[:build_url.rfind('/')].rfind('/') + 1: build_url.rfind('/')]

        build_slow_url = build_url + 'testReport/api/json?depth=2'
        build_fast_url = build_url + 'testReport/api/json?tree=suites[cases[className,name,duration,status,skipped]]'

        if not verify_test_report_exist(build_slow_url):
            logging.info("build has no test report, skip:" + build_slow_url)
            continue

        logging.info('parsing test report result for build:' + build_fast_url)
        test_response = json.loads(requests.get(build_fast_url).text)
        if 'junit.TestResult' not in test_response['_class']:
            test_response = json.loads(requests.get(build_slow_url).text)

        out_file = os.path.join(output_directory, build_no + '_detail_bk.json')
        if not os.path.exists(out_file):
            output_detail_file = open(out_file, 'w')
            output_detail_file.write(json.dumps(test_response, indent=4, sort_keys=True))
            output_detail_file.close()
            logging.info("store raw crawl info as json to :" + output_detail_file.name)

        out = os.path.join(output_directory, build_no+'.csv')
        if os.path.exists(out):
            continue
        with open(out, 'w') as of:
            file_writer = csv.writer(of)
            file_writer.writerow(['ClassName','Duration'])

            cases = test_response['suites']
            for case in cases:
                class_duration = 0
                class_name = ""
                for tests in case['cases']:
                    class_duration += tests['duration']
                    class_name = tests['className']
                file_writer.writerow([class_name, str(class_duration)])
        of.close()
        logging.info("test result saved to file: " + out)


def create_output_directory(project):
    # create output folder for the project: output/project_name
    if not os.path.isdir('output'):
        os.mkdir('output')
    output_path = os.path.join('output',project)
    if not os.path.isdir(output_path):
        os.mkdir(output_path)
    return output_path


def main(argv):
    parser = argparse.ArgumentParser(description='crawl test result from jenkins')
    parser.add_argument('url', type=str, metavar='jenkins_url',help='url in jenkins')
    parser.add_argument('job_info',type=str, metavar="job_name",help='The job name you want to crawl. e.g.Hive-linux-ARM-trunk ')
    parser.add_argument('project_name',type=str,metavar='project_name', help='name of the project. e.g. hive')
    args = parser.parse_args(argv)

    url = args.url
    job_info = args.job_info
    project_name = args.project_name

    output_directory = create_output_directory(project_name)

    if not url.endswith('/'):
        url += '/'
    jenkins_url = url + 'job/' + job_info + '/api/json?depth=2'
    builds = get_build(jenkins_url, output_directory)
    print()


    if project_name == 'CXF' or project_name == 'bookkeeper':
        get_test_report_cxf(builds, output_directory)

    else:
        get_test_report(builds, output_directory)


if __name__ == '__main__':
    logging.getLogger().setLevel(getattr(logging, 'INFO'))
    # sys.argv = ['jenkins.py','https://builds.apache.org/view/H-L/view/Hive/', 'Hive-linux-ARM-trunk', 'hive']
    # sys.argv = ['jenkins.py','https://builds.apache.org/view/C/view/Apache%20CXF/','CXF-Master-JDK15','CXF']
    # sys.argv = ['jenkins.py', 'https://jenkins.webtide.net/job/nightlies/', 'jetty-10.0.x-windows-nightly', 'jetty']
    sys.argv = ['jenkins.py', 'https://ci.eclipse.org/californium/', 'californium-master-nightly', 'californium']
    main(sys.argv[1:])
